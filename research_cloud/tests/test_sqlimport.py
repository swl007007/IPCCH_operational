"""Input import: name preflight, identifier/precision typing, whole-table verification, rollback, report merge.

Database tests need a disposable PostgreSQL given by RC_TEST_PG (libpq string without dbname, superuser)."""
import contextlib
import hashlib
import json
import os
import tempfile
import unittest
import uuid

from research_cloud.sqlimport import load_inputs as li

PG = os.environ.get("RC_TEST_PG")
INVENTORY = "/home/swl007007/projects/food-crisis-research/scratch/p1/input-inventory.json"


class Names(unittest.TestCase):
    def test_similar_long_ids_get_distinct_names_within_63_bytes(self):
        ids = [f"ipcch.model_ready.origin_safe_climate_idp_v1_history_ledger_h{h}.csv" for h in ("0", "3", "6", "12")]
        names = li.plan_names([("ipcch", {"id": i}) for i in ids])
        tables = [t for _, t in names.values()]
        self.assertEqual(len(set(tables)), 4)
        self.assertTrue(all(len((t + li.SIDE).encode()) <= 63 for t in tables))

    @unittest.skipUnless(os.path.exists(INVENTORY), "inventory not present")
    def test_whole_inventory_preflight(self):
        entries = li.expected_entries(json.load(open(INVENTORY)))
        self.assertEqual(len(li.plan_names(entries)), len(entries))

    def test_identifier_columns_stay_text(self):
        for name in ("area_id", "FEWSNET_admin_code", "admin_code", "fid", "region_id", "country_code"):
            self.assertTrue(li.is_identifier(name, set()), name)
        self.assertFalse(li.is_identifier("rainfall", set()))
        self.assertFalse(li.is_identifier("date", {"date"}))


BIG = "9007199254740993"          # 2**53 + 1: not exactly representable as a double


def cross_chunk_csv(big_first, n_small, extra_ints=()):
    """area_id + v (one big integer and one fraction on opposite sides of a CHUNK boundary, small integers between)
    + n (pure integers incl. 16-18 digits) + d (small integers, then a fraction: an ordinary double column)."""
    first, last = (BIG, "0.5") if big_first else ("0.5", BIG)
    rows = [(first, "1")] + [("1", "1")] * n_small + [(last, "2.5")]
    ints = list(extra_ints) or ["123456789012345678"]
    lines = ["area_id,v,n,d"] + [f"{i},{v},{ints[i % len(ints)]},{d}" for i, (v, d) in enumerate(rows, 1)]
    return "\n".join(lines) + "\n"


class CrossChunk(unittest.TestCase):
    """A01: an integer that a double cannot hold, seen in any chunk, keeps a later double column as text."""

    def infer(self, text, chunk):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "f.csv")
        open(path, "w").write(text)
        original = li.CHUNK
        li.CHUNK = chunk
        try:
            header = li.read_header(path)
            return li.infer_types(path, header, set(), li.short_rows(path, header))[0]
        finally:
            li.CHUNK = original

    def test_both_orders_across_a_small_chunk_boundary(self):
        for big_first in (True, False):
            kinds = self.infer(cross_chunk_csv(big_first, n_small=5), chunk=4)
            self.assertEqual(kinds["v"], "text", f"big_first={big_first}")
            self.assertEqual(kinds["n"], "bigint")               # pure integers (<= 18 digits) unchanged
            self.assertEqual(kinds["d"], "double precision")     # small integers then a fraction: still double

    def test_big_integer_before_the_real_chunk_boundary(self):
        kinds = self.infer(cross_chunk_csv(True, n_small=li.CHUNK), chunk=li.CHUNK)
        self.assertEqual((kinds["v"], kinds["n"], kinds["d"]), ("text", "bigint", "double precision"))

    def test_safe_integers_before_a_fraction_stay_double(self):
        kinds = self.infer(cross_chunk_csv(True, n_small=5).replace(BIG, "900719925474099"), chunk=4)
        self.assertEqual(kinds["v"], "double precision")         # 15 digits, below 2**53: exactly representable


@unittest.skipUnless(PG, "RC_TEST_PG not set")
class Load(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg2
        cls.db = "imp_" + uuid.uuid4().hex[:10]
        admin = psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f"CREATE DATABASE {cls.db}")
        admin.close()
        cls.dsn = f"{PG} dbname={cls.db}"

    @classmethod
    def tearDownClass(cls):
        import psycopg2
        admin = psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f"DROP DATABASE {cls.db} WITH (FORCE)")
        admin.close()

    def entry(self, text, eid="fewsnet.fixture"):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "f.csv")
        open(path, "w").write(text)
        sha = hashlib.sha256(open(path, "rb").read()).hexdigest()
        return {"id": eid, "path": path, "actual_sha256": sha, "actual_bytes": os.path.getsize(path),
                "proposed_storage": "Cloud SQL table + GCS original object", "file_type": "csv"}

    def connect(self):
        import psycopg2
        return contextlib.closing(psycopg2.connect(self.dsn))

    def test_typing_and_whole_table_verification(self):
        text = ("area_id,big,mixed,x,label\n"
                "101,12345678901234567890,1.5,0.1,a\n"
                "102,1,9007199254740993,,b\n"
                "103,2,2.25,3e-5,\n"
                "System.IO.MemoryStream\n")
        e = self.entry(text)
        with self.connect() as conn:
            r = li.load_one(conn, e, "fewsnet", li.table_name(e["id"]), None)
        catalog = {}
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT source_header, sql_type FROM public._column_catalog WHERE table_name = %s", (r["table"],))
            catalog = dict(cur.fetchall())
            cur.execute(f'SELECT count(*) FROM fewsnet."{li.table_name(e["id"])}{li.SIDE}"')
            side_rows = cur.fetchone()[0]
        self.assertEqual(catalog, {"area_id": "text", "big": "text", "mixed": "text", "x": "double precision", "label": "text"})
        self.assertEqual((r["status"], r["typed_rows"], side_rows, r["cell_comparison"]["cells_compared"]), ("verified", 3, 1, 15))
        self.assertEqual(r["empty_to_null_numeric"], {"x": 1})

    def test_cross_chunk_big_integer_round_trips_verbatim(self):
        """A01, both row orders across a CHUNK boundary: the stored value is the original integer text, read back
        before any float conversion; the pure-integer column stays bigint."""
        original = li.CHUNK
        li.CHUNK = 4
        try:
            for big_first in (True, False):
                e = self.entry(cross_chunk_csv(big_first, n_small=5), f"fewsnet.a01_{int(big_first)}")
                table = li.table_name(e["id"])
                with self.connect() as conn:
                    r = li.load_one(conn, e, "fewsnet", table, None)
                big_row = 1 if big_first else 7
                with self.connect() as conn, conn.cursor() as cur:
                    cur.execute("SELECT source_header, sql_type FROM public._column_catalog WHERE table_name = %s", (r["table"],))
                    catalog = dict(cur.fetchall())
                    cur.execute(f'SELECT v::text, n::text FROM fewsnet."{table}" WHERE _source_row = %s', (big_row,))
                    v, n = cur.fetchone()
                self.assertEqual(r["status"], "verified")
                self.assertEqual((catalog["v"], catalog["n"], catalog["d"]), ("text", "bigint", "double precision"))
                self.assertEqual((v, n), (BIG, "123456789012345678"), f"big_first={big_first}")
        finally:
            li.CHUNK = original

    def test_failed_verification_commits_nothing(self):
        e = self.entry("area_id,v\n1,0.5\n", "fewsnet.rollback")
        original = li.compare_table
        li.compare_table = lambda *a: {"cells_compared": 2, "mismatched_columns": [{"column": "v", "count": 1}]}
        try:
            with self.connect() as conn:
                with self.assertRaises(li.ImportFailure):
                    li.load_one(conn, e, "fewsnet", li.table_name(e["id"]), None)
                conn.rollback()
        finally:
            li.compare_table = original
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT to_regclass(%s)", (f'fewsnet."{li.table_name(e["id"])}"',))
            self.assertIsNone(cur.fetchone()[0])

    def test_only_merges_into_the_report_and_reconciles_the_full_set(self):
        a, b = self.entry("area_id,v\n1,0.5\n", "ipcch.a"), self.entry("area_id,v\n2,1.5\n", "ipcch.b")
        d = tempfile.mkdtemp()
        json.dump({"namespaces": {"ipcch": {"files": [a, b]}}}, open(f"{d}/inv.json", "w"))
        open(f"{d}/keys.jsonl", "w").write("")
        args = ["--inventory", f"{d}/inv.json", "--keys", f"{d}/keys.jsonl", "--dsn", self.dsn, "--report", f"{d}/r.json"]
        self.assertEqual(li.main(args + ["--only", "ipcch.a"]), 1)         # b not imported yet
        rep = json.load(open(f"{d}/r.json"))
        self.assertEqual((rep["reconciliation"]["verified"], rep["reconciliation"]["not_imported"]), (["ipcch.a"], ["ipcch.b"]))
        self.assertEqual(li.main(args + ["--only", "ipcch.b"]), 0)         # merged: both verified
        self.assertEqual(json.load(open(f"{d}/r.json"))["reconciliation"]["verified"], ["ipcch.a", "ipcch.b"])

    def test_exact_integers_floats_and_one_unit_corruption(self):
        text = "area_id,n,x\n1,9007199254740993,-7961314590657215.0\n2,,0.1\n3,123456789012345678,1e-5\n"
        e = self.entry(text, "fewsnet.precision")
        tname = li.table_name(e["id"])
        with self.connect() as conn:
            r = li.load_one(conn, e, "fewsnet", tname, None)
        self.assertEqual(r["column_types"], {"bigint": 1, "double precision": 1, "text": 1})
        header, kinds = ["area_id", "n", "x"], {"area_id": "text", "n": "bigint", "x": "double precision"}
        with self.connect() as conn, conn.cursor() as cur:
            table = f'fewsnet."{tname}"'
            cur.execute(f"UPDATE {table} SET n = n + 1 WHERE _source_row = 1")   # one unit beyond float precision
            got = li.compare_table(cur, table, e["path"], header, kinds, header, set())
            conn.rollback()
        self.assertEqual(got["mismatched_columns"], [{"column": "n", "count": 1, "first_source_row": 1}])

    def test_blank_line_and_short_row_reconcile_with_the_key_profile(self):
        e = self.entry("admin_code,year,v\n1,2020,0.5\n\n2,2021,1.5\nSystem.IO.MemoryStream\n", "fewsnet.short")
        profile = {"key_columns": ["admin_code", "year"], "key_duplicates_full": 0, "key_null_or_empty": 2}
        with self.connect() as conn:
            r = li.load_one(conn, e, "fewsnet", li.table_name(e["id"]), profile)
        self.assertEqual((r["typed_rows"], r["irregular_rows"]["count"], r["irregular_rows"]["rows"]), (2, 2, [2, 4]))
        self.assertTrue(r["keys"]["agrees_with_profile"])

    def test_receipt_for_changed_bytes_is_stale(self):
        entry = {"id": "ipcch.a", "actual_sha256": "new"}
        names = {"ipcch.a": ("ipcch", li.table_name("ipcch.a"))}
        self.assertFalse(li.current({"sha256": "old", "table": "ipcch." + li.table_name("ipcch.a")}, entry, names))
        self.assertFalse(li.current({"sha256": "new", "table": "ipcch.a_old_name"}, entry, names))
        self.assertTrue(li.current({"sha256": "new", "table": "ipcch." + li.table_name("ipcch.a")}, entry, names))


if __name__ == "__main__":
    unittest.main()
