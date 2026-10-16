import json
import os
import sqlite3
import tempfile
import unittest

from research_cloud.inventory import registry_ledger as rl


def fixture_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
      CREATE TABLE model_versions (name TEXT, version INT, source TEXT, status TEXT);
      CREATE TABLE logged_models (model_id TEXT, experiment_id INT, source_run_id TEXT);
      CREATE TABLE logged_model_tags (model_id TEXT, tag_key TEXT, tag_value TEXT);
      CREATE TABLE tags (run_uuid TEXT, key TEXT, value TEXT);
      INSERT INTO model_versions VALUES ('A',1,'models:/m-a','READY'), ('A',2,'models:/m-b','READY'),
                                        ('B',1,'runs:/r/legacy','READY'), ('C',1,'models:/m-c','READY');
      INSERT INTO logged_models VALUES ('m-a',2,'r1'), ('m-b',2,'r2'), ('m-c',2,'r3');
      INSERT INTO logged_model_tags VALUES ('m-a','family','fam'), ('m-b','family','fam'),
                                           ('m-c','family','fam');
      INSERT INTO tags VALUES ('r3','zz_prov.arm_kind','reused_comparator');
    """)
    db.commit()
    return db


class LedgerCoverage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db = fixture_db(os.path.join(self.tmp, "s.db"))

    def test_unresolved_source_is_kept_and_keys_match(self):
        rows = rl.build_rows(self.db, {"fam": {"x": "missing"}}, {}, {}, {}, {})
        rl.check_keys(self.db, rows)
        by_key = {(r["registered_model"], r["version"]): r for r in rows}
        self.assertEqual(len(rows), 4)
        self.assertEqual(by_key[("B", 1)]["ledger_class"], "unresolved_registry_identity")
        self.assertEqual(by_key[("A", 2)]["ledger_class"], "missing_weights_tracking_only")

    def test_reused_comparator_needs_resolution_despite_missing_family_members(self):
        rows = rl.build_rows(self.db, {"fam": {"x": "missing"}}, {}, {}, {}, {})
        c = [r for r in rows if r["registered_model"] == "C"][0]
        self.assertEqual(c["ledger_class"], "needs_resolution")
        rows = rl.build_rows(self.db, {"fam": {"x": "missing"}}, {}, {}, {},
                             {"m-c": {"ledger_class": "weights_retained_package_pending", "evidence": "linked"}})
        self.assertEqual([r for r in rows if r["registered_model"] == "C"][0]["ledger_class"], "weights_retained_package_pending")

    def test_key_mismatch_is_fatal(self):
        rows = rl.build_rows(self.db, {"fam": {}}, {}, {}, {}, {})
        with self.assertRaises(SystemExit):
            rl.check_keys(self.db, rows[:-1])
        with self.assertRaises(SystemExit):
            rl.check_keys(self.db, rows + rows[:1])


if __name__ == "__main__":
    unittest.main()
