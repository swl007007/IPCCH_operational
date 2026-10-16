"""Spend ledger: atomic separate-pool admission; reservations held until provider terminal status."""
import os
import sqlite3
import tempfile
import threading
import unittest

from research_cloud.cost import ledger as L


class Ledger(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "ledger.sqlite")
        self.conn = L.connect(self.path)

    def test_pools_are_separate_and_cap_is_enforced(self):
        L.reserve(self.conn, "training", "2026-10", "t1", 99.0, {})
        with self.assertRaises(L.AdmissionRefused):
            L.reserve(self.conn, "training", "2026-10", "t2", 1.5, {})
        L.reserve(self.conn, "platform", "2026-10", "p1", 99.0, {})     # the other pool is untouched
        L.reserve(self.conn, "training", "2026-11", "t3", 99.0, {})     # months are separate
        self.assertIsNone(self.conn.execute("SELECT 1 FROM operations WHERE operation_id='t2'").fetchone())

    def test_reservation_held_until_terminal_then_actual_counts(self):
        L.reserve(self.conn, "training", "2026-10", "hpt", 0.2, {"job": "smoke"})
        L.attach(self.conn, "hpt", "projects/food-crisis-modeling-enso/locations/us-central1/hyperparameterTuningJobs/1")
        for state in ("JOB_STATE_RUNNING", "JOB_STATE_CANCELLING"):
            self.assertFalse(L.observe(self.conn, "hpt", state, "describe"))
            with self.assertRaises(L.LedgerError):
                L.settle(self.conn, "hpt", 0.1, "estimate")
        with self.assertRaises(L.LedgerError):            # a submitted job cannot be released
            L.release(self.conn, "hpt", "lookup")
        self.assertTrue(L.observe(self.conn, "hpt", "JOB_STATE_CANCELLED", "describe"))
        L.settle(self.conn, "hpt", 0.35, "duration estimate")             # above the reservation: actual counts
        self.assertAlmostEqual(L.summary(self.conn, "2026-10")["training"]["committed_usd"], 0.35)

    def test_release_needs_evidence_of_no_resource(self):
        L.reserve(self.conn, "training", "2026-10", "x", 1.0, {})
        with self.assertRaises(L.LedgerError):
            L.release(self.conn, "x", "")
        L.release(self.conn, "x", "jobs list: no job with this display name")
        self.assertEqual(L.summary(self.conn, "2026-10")["training"]["committed_usd"], 0.0)

    def test_concurrent_admission_never_overcommits(self):
        results = []

        def admit(i):
            conn = L.connect(self.path)
            try:
                L.reserve(conn, "training", "2026-10", f"c{i}", 30.0, {})
                results.append(True)
            except (L.AdmissionRefused, sqlite3.OperationalError):
                results.append(False)
        threads = [threading.Thread(target=admit, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(results), 3)
        self.assertLessEqual(L.summary(self.conn, "2026-10")["training"]["committed_usd"], 100.0)

    def test_vertex_reservation_arithmetic(self):
        r = L.vertex_reservation(0.21849885, 2, 900, 0, 100, 0.000063014)
        self.assertAlmostEqual(r["total_usd"], 0.112400125, places=9)            # supervisor baseline
        r = L.vertex_reservation(0.21849885, 2, 900, 301, 100, 0.000063014)
        self.assertEqual(r["billed_seconds_per_trial"], 1230)                   # rounded up to 30 s


if __name__ == "__main__":
    unittest.main()


class Atomicity(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "ledger.sqlite")
        self.conn = L.connect(self.path)

    def test_attach_cannot_interleave_with_release(self):
        """release's deciding read and its write are one exclusive transaction: an attach from another connection
        between them is blocked (it cannot land), so the operation is never released with a live resource."""
        L.reserve(self.conn, "training", "2026-10", "op", 100.0, {})
        other = L.connect(self.path, timeout=0.2)
        real_get, seen = L._get, []

        def interleaving_get(conn, operation_id):
            row = real_get(conn, operation_id)
            if not seen:
                seen.append(True)
                try:
                    L.attach(other, operation_id, "projects/p/locations/l/customJobs/1")
                    seen.append("attached")
                except sqlite3.OperationalError:
                    seen.append("blocked")
            return row
        L._get = interleaving_get
        try:
            L.release(self.conn, "op", "lookup: none")
        finally:
            L._get = real_get
        self.assertEqual(seen[1], "blocked")
        status, resource = self.conn.execute("SELECT status, provider_resource FROM operations").fetchone()
        self.assertEqual((status, resource), ("released", None))
        with self.assertRaises(L.LedgerError):                 # and a later attach sees the release
            L.attach(other, "op", "projects/p/locations/l/customJobs/1")

    def test_attach_first_blocks_release(self):
        L.reserve(self.conn, "training", "2026-10", "op", 1.0, {})
        L.attach(self.conn, "op", "projects/p/locations/l/customJobs/2")
        with self.assertRaises(L.LedgerError):
            L.release(L.connect(self.path), "op", "lookup: none")

    def test_invalid_caps_and_quantities_are_refused(self):
        for cap in (float("inf"), float("nan"), 0, -5, True):
            with self.assertRaises(L.LedgerError):
                L.connect(os.path.join(tempfile.mkdtemp(), "x.sqlite"), pools={"training": cap})
        with self.assertRaises(L.LedgerError):
            L.connect(self.path, pools={"training": 1e6})        # an existing cap is not silently replaced
        for amount in (float("inf"), float("nan"), 0, -1):
            with self.assertRaises(L.LedgerError):
                L.reserve(self.conn, "training", "2026-10", f"a{amount}", amount, {})
        bad = [dict(disk_gib=-100), dict(trials=0), dict(trials=1.5), dict(timeout_s=0), dict(overhead_s=-1),
               dict(rate_per_hour=float("nan")), dict(disk_rate_gib_hour=-1e-6)]
        base = dict(rate_per_hour=0.21849885, trials=2, timeout_s=900, overhead_s=0, disk_gib=100, disk_rate_gib_hour=0.000063014)
        for change in bad:
            with self.assertRaises(L.LedgerError):
                L.vertex_reservation(**{**base, **change})
