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
