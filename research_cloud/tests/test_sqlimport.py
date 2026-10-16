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


if __name__ == "__main__":
    unittest.main()
