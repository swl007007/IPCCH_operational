"""Geometry import helpers: COPY text escaping, typed comparison and bundle selection refusals."""
import unittest

from research_cloud.sqlimport import load_geometry as lg


class Helpers(unittest.TestCase):
    def test_copy_text_round_trip_and_null(self):
        for value in ("a\tb", "line\nnext\r", "back\\slash", "", "Côte d'Ivoire"):
            self.assertEqual(lg.unescape(lg.escape(value)), value)
        self.assertIsNone(lg.unescape(lg.escape(None)))
        self.assertIsNone(lg.render(float("nan"), "float"))
        self.assertEqual(lg.render(3.0, "int"), "3")

    def test_typed_comparison_is_exact(self):
        self.assertTrue(lg.same("2397758870.74", "2397758870.74", "float"))
        self.assertTrue(lg.same("1e-05", "1e-05", "float") and lg.same("100.0", "100", "float"))
        self.assertFalse(lg.same("0.1", "0.10000000000000002", "float"))
        self.assertFalse(lg.same(None, "", "text"))
        self.assertFalse(lg.same("SS", "SS ", "text"))

    def test_bundle_needs_one_postgis_shp(self):
        member = {"bundle": "b", "file_type": "dbf"}
        inv = {"namespaces": {"x": {"files": [member, {"bundle": "b", "file_type": "shp", "proposed_storage": "GCS-only object"}]}}}
        with self.assertRaises(lg.GeometryImportFailure):
            lg.bundle_entries(inv, "b")
        inv["namespaces"]["x"]["files"][1]["proposed_storage"] = lg.POSTGIS_STORAGE
        inv["namespaces"]["x"]["files"].append({"bundle": "b", "file_type": "csv"})
        (ns, shp), members = lg.bundle_entries(inv, "b")
        self.assertEqual((ns, len(members)), ("x", 2))   # the csv sidecar is not a shapefile member


if __name__ == "__main__":
    unittest.main()


PG = __import__("os").environ.get("RC_TEST_PG")


@unittest.skipUnless(PG, "RC_TEST_PG not set")
class RoundTrip(unittest.TestCase):
    """load() against a throwaway database with PostGIS: verified commit, and rollback when verification fails."""

    @classmethod
    def setUpClass(cls):
        import uuid
        import psycopg2
        cls.db = "geo_" + uuid.uuid4().hex[:10]
        admin = psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f"CREATE DATABASE {cls.db}")
        admin.close()
        cls.dsn = f"{PG} dbname={cls.db}"
        with psycopg2.connect(cls.dsn) as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION postgis")

    @classmethod
    def tearDownClass(cls):
        import psycopg2
        admin = psycopg2.connect(PG + " dbname=postgres")
        admin.autocommit = True
        admin.cursor().execute(f"DROP DATABASE {cls.db} WITH (FORCE)")
        admin.close()

    def export_dir(self, bundle, declared_rows=None):
        import json
        import os
        import struct
        import tempfile
        d = tempfile.mkdtemp()
        point = lambda x, y: (struct.pack("<BIdd", 1, 1, x, y)).hex()
        square = (struct.pack("<BII", 1, 3, 1) + struct.pack("<I", 5)
                  + b"".join(struct.pack("<dd", *p) for p in [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])).hex()
        rows = [["0", lg.escape("tab\there"), "1", "0.1", point(30.5, -1.25)],
                ["1", r"\N", r"\N", r"\N", square]]
        with open(f"{d}/rows.tsv", "w", newline="\n") as f:
            f.writelines("\t".join(r) + "\n" for r in rows)
        record = {"bundle": bundle, "namespace": "fx", "table": "t_" + bundle, "srid": 4326, "prj": "GEOGCS[...]",
                  "has_z": False, "rows": declared_rows or 2, "columns": [
                      {"name": "name", "kind": "text", "sql_type": "text"}, {"name": "n", "kind": "int", "sql_type": "bigint"},
                      {"name": "v", "kind": "float", "sql_type": "double precision"}],
                  "geometry_types": {"Point": 1, "Polygon": 1}, "members": {}, "inventory": {"path": "inv", "sha256": "0" * 64},
                  "rows_sha256": lg.sha256_file(f"{d}/rows.tsv")}
        with open(f"{d}/export.json", "w") as f:
            json.dump(record, f)
        return d

    def query(self, sql):
        import psycopg2
        with psycopg2.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    def test_verified_round_trip_commits_with_identity(self):
        import tempfile
        r = lg.load(self.export_dir("ok"), self.dsn, tempfile.mktemp())
        self.assertEqual((r["status"], r["rows"], r["wkb_byte_equal"]), ("verified", 2, True))
        self.assertEqual(self.query("SELECT name, n, v, ST_AsText(geom) FROM fx.t_ok ORDER BY _fid"),
                         [("tab\there", 1, 0.1, "POINT(30.5 -1.25)"), (None, None, None, "POLYGON((0 0,1 0,1 1,0 1,0 0))")])
        self.assertEqual(self.query("SELECT export_sha256 = %r FROM public._geometry_bundles WHERE bundle = 'ok'"
                                    % r["export_json_sha256"]), [(True,)])

    def test_failed_verification_rolls_everything_back(self):
        import tempfile
        r = lg.load(self.export_dir("bad", declared_rows=3), self.dsn, tempfile.mktemp())
        self.assertEqual(r["status"], "failed")
        self.assertEqual(self.query("SELECT to_regclass('fx.t_bad') IS NULL"), [(True,)])
        if self.query("SELECT to_regclass('public._geometry_bundles') IS NOT NULL") == [(True,)]:
            self.assertEqual(self.query("SELECT count(*) FROM public._geometry_bundles WHERE bundle = 'bad'"), [(0,)])

    def test_changed_rows_file_is_refused_before_any_ddl(self):
        import tempfile
        d = self.export_dir("tampered")
        open(f"{d}/rows.tsv", "a").write("2\tx\t1\t1.0\t\\N\n")
        with self.assertRaises(lg.GeometryImportFailure):
            lg.load(d, self.dsn, tempfile.mktemp())
        self.assertEqual(self.query("SELECT to_regclass('fx.t_tampered') IS NULL"), [(True,)])
