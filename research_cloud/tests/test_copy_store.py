"""copy_store tests. Digest tests are pure; the integration tests need a disposable
PostgreSQL server given by RC_TEST_PG (libpq string without dbname, superuser)."""
import os
import sqlite3
import tempfile
import unittest
import uuid

from research_cloud.mlflow_migrate import copy_store as cs

PG = os.environ.get("RC_TEST_PG")


class DigestIsUnambiguous(unittest.TestCase):
    def test_null_vs_literal_backslash_n(self):
        self.assertNotEqual(cs.digest([(None,)], ["text"]), cs.digest([("\\N",)], ["text"]))

    def test_separator_characters_do_not_shift_columns(self):
        types = ["text", "text"]
        self.assertNotEqual(cs.digest([("a\x1fb", "c")], types), cs.digest([("a", "b\x1fc")], types))

    def test_record_separator_does_not_merge_rows(self):
        types = ["text"]
        self.assertNotEqual(cs.digest([("a\x1eb",)], types), cs.digest([("a",), ("b",)], types))

    def test_bool_int_float_typed(self):
        self.assertEqual(cs.digest([(1, 1.0)], ["boolean", "double precision"]),
                         cs.digest([(True, 1.0)], ["boolean", "double precision"]))
        self.assertNotEqual(cs.digest([(1.0,)], ["double precision"]), cs.digest([(1.0000000000000002,)], ["double precision"]))

    def test_order_independent(self):
        self.assertEqual(cs.digest([("a",), ("b",)], ["text"]), cs.digest([("b",), ("a",)], ["text"]))


@unittest.skipUnless(PG, "RC_TEST_PG not set")
class CopyStoreIntegration(unittest.TestCase):
    def setUp(self):
        import psycopg2
        self.psycopg2 = psycopg2
        self.db = "rc_test_" + uuid.uuid4().hex[:8]
        admin = psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f'CREATE DATABASE "{self.db}"')
        admin.close()
        self.dsn = PG + f" dbname={self.db}"
        with psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)")
            cur.execute("INSERT INTO alembic_version VALUES ('rev1')")
            cur.execute("CREATE TABLE parent (id serial PRIMARY KEY, name text, flag boolean, v double precision)")
            cur.execute("CREATE TABLE child (id integer PRIMARY KEY, parent_id integer REFERENCES parent(id), note text)")
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "src.db")
        self.make_source(self.src, note="x")

    def tearDown(self):
        admin = self.psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f'DROP DATABASE IF EXISTS "{self.db}"')
        admin.close()

    @staticmethod
    def make_source(path, note):
        if os.path.exists(path):
            os.unlink(path)
        s = sqlite3.connect(path)
        s.execute("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)")
        s.execute("INSERT INTO alembic_version VALUES ('rev1')")
        s.execute("CREATE TABLE parent (id integer PRIMARY KEY, name text, flag boolean, v float)")
        s.execute("CREATE TABLE child (id integer PRIMARY KEY, parent_id integer REFERENCES parent(id), note text)")
        s.executemany("INSERT INTO parent VALUES (?,?,?,?)", [(1, "\\N", 1, 0.1), (2, None, 0, float("nan")), (7, "a\x1fb", None, -2.5)])
        s.executemany("INSERT INTO child VALUES (?,?,?)", [(1, 1, note), (2, 7, None)])
        s.commit()
        s.close()

    def run_copy(self, *extra):
        report = os.path.join(self.tmp, uuid.uuid4().hex + ".json")
        rc = cs.main(["--source", self.src, "--target", self.dsn, "--report", report, *extra])
        import json
        with open(report) as handle:
            return rc, json.load(handle)

    def test_interrupt_resume_verify_and_sequence(self):
        rc, rep = self.run_copy("--stop-after-tables", "1")
        self.assertEqual(rep.get("stopped_early"), "child")
        rc, rep = self.run_copy()
        self.assertEqual(rc, 0)
        self.assertEqual(rep["tables"]["parent"]["status"], "skipped_complete")
        rc, rep = self.run_copy("--verify-only")
        self.assertEqual((rc, rep["verified"]), (0, True))
        with self.psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("INSERT INTO parent (name) VALUES ('new') RETURNING id")
            self.assertEqual(cur.fetchone()[0], 8)  # sequence advanced past max(id)=7

    def test_same_size_corruption_detected(self):
        self.assertEqual(self.run_copy()[0], 0)
        with self.psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("UPDATE child SET note='y' WHERE id=1")  # same length as 'x'
        rc, rep = self.run_copy("--verify-only")
        self.assertEqual(rc, 1)
        self.assertFalse(rep["tables"]["child"]["match"])

    def test_changed_snapshot_refused_before_writes(self):
        self.run_copy("--stop-after-tables", "1")
        self.make_source(self.src, note="different")
        rc, rep = self.run_copy()
        self.assertEqual(rc, 1)
        self.assertIn("different source snapshot", rep["error"])
        with self.psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("SELECT count(*) FROM child")
            self.assertEqual(cur.fetchone()[0], 0)

    def test_generated_column_values_are_compared(self):
        with self.psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("CREATE TABLE gen (id integer PRIMARY KEY, a bigint, b bigint, d bigint GENERATED ALWAYS AS (b - a) STORED)")
        s = sqlite3.connect(self.src)
        s.execute("CREATE TABLE gen (id integer PRIMARY KEY, a bigint, b bigint, d bigint GENERATED ALWAYS AS (b - a) VIRTUAL)")
        s.executemany("INSERT INTO gen (id, a, b) VALUES (?,?,?)", [(1, 5, 9), (2, None, 3)])
        s.commit(); s.close()
        rc, rep = self.run_copy()
        self.assertEqual(rc, 0)
        self.assertEqual(rep["tables"]["gen"]["generated_columns_recomputed_and_compared"], ["d"])
        self.assertTrue(self.run_copy("--verify-only")[1]["tables"]["gen"]["match"])

    def test_generated_expression_mismatch_fails(self):
        with self.psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("CREATE TABLE gen (id integer PRIMARY KEY, a bigint, b bigint, d bigint GENERATED ALWAYS AS (a - b) STORED)")
        s = sqlite3.connect(self.src)
        s.execute("CREATE TABLE gen (id integer PRIMARY KEY, a bigint, b bigint, d bigint GENERATED ALWAYS AS (b - a) VIRTUAL)")
        s.execute("INSERT INTO gen (id, a, b) VALUES (1, 5, 9)")
        s.commit(); s.close()
        rc, rep = self.run_copy()
        self.assertEqual(rc, 1)
        self.assertIn("digest mismatch after loading gen", rep["error"])

    def test_verify_only_writes_nothing(self):
        rc, rep = self.run_copy("--verify-only")
        with self.psycopg2.connect(self.dsn) as c, c.cursor() as cur:
            cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_name LIKE '\\_rc\\_%'")
            self.assertEqual(cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
