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
