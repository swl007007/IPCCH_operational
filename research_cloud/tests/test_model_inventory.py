import unittest

from research_cloud.inventory.model_inventory import attach_candidates, declared_roots, resolve

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

    def test_no_candidates_is_an_error(self):
        with self.assertRaises(ValueError):
            resolve(member())


def fake_state(table):
    return lambda paths: {p: dict(table[p], path=p) for p in paths}


class CandidateConstructionPropagatesRootFailures(unittest.TestCase):
    """Drives declared_roots -> attach_candidates -> resolve with an injected path-state function."""

    def run_member(self, root_states, member_states):
        roots = declared_roots(list(root_states), fake_state(root_states))
        fam = {"roots": roots, "members": [dict(REC, path="models/x.ubj")]}
        attach_candidates([fam], fake_state(member_states))
        return resolve(fam["members"][0])

    def test_unreadable_second_root_is_not_lost_when_first_lacks_member(self):
        status = self.run_member({"/temp": {"status": "local"}, "/preserved": {"status": "inspection_error"}},
                                 {"/temp/models/x.ubj": {"status": "missing"}})
        self.assertEqual(status, ("inspection_error", None))

    def test_cloud_only_root_propagates(self):
        status = self.run_member({"/temp": {"status": "local"}, "/dbx": {"status": "cloud_only"}},
                                 {"/temp/models/x.ubj": {"status": "missing"}})
        self.assertEqual(status, ("cloud_only", None))

    def test_missing_only_when_every_root_or_member_not_found(self):
        status = self.run_member({"/temp": {"status": "local"}, "/gone": {"status": "missing"}},
                                 {"/temp/models/x.ubj": {"status": "missing"}})
        self.assertEqual(status, ("missing", None))

    def test_all_declared_roots_become_candidates(self):
        roots = declared_roots(["/a", "/b"], fake_state({"/a": {"status": "local"}, "/b": {"status": "missing"}}))
        fam = {"roots": roots, "members": [dict(REC, path="m")]}
        attach_candidates([fam], fake_state({"/a/m": {"status": "missing"}}))
        self.assertEqual([c["status"] for c in fam["members"][0]["candidates"]], ["missing", "root_missing"])


if __name__ == "__main__":
    unittest.main()
