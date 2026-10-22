"""Self-checks for the P1 crosswalk scripts on tiny synthetic inputs.

Run: python -m unittest test_crosswalk_selfcheck.py  (from this directory)
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

import crosswalk_decide
from crosswalk_cs_labels import record_checks
from crosswalk_decide import strict_matches


def fdw(rows):
    return gpd.GeoDataFrame(
        pd.DataFrame(rows, columns=["id", "fnid", "value", "country_code", "reporting_date"]),
        geometry=[box(0, 0, 1, 1)] * len(rows), crs=4326)


def hdx(rows):
    return pd.DataFrame(rows, columns=["id", "fnid", "phase", "roster_iso2", "month"])


class RecordChecks(unittest.TestCase):
    def run_checks(self, units, month_hdx, freeze=None):
        freeze = month_hdx if freeze is None else freeze
        return record_checks(units, month_hdx, "2026-06", freeze["id"].value_counts())

    def test_valid_record_passes(self):
        out = self.run_checks(fdw([["1", "A", 3.0, "SO", "2026-06-01"]]),
                              hdx([["1", "A", 3.0, "SO", "2026-06"]]))
        self.assertEqual(out["passing_ids"], {"1"})

    def test_duplicate_fdw_id_fails(self):
        out = self.run_checks(fdw([["1", "A", 3.0, "SO", "2026-06-01"],
                                   ["1", "A", 3.0, "SO", "2026-06-01"]]),
                              hdx([["1", "A", 3.0, "SO", "2026-06"]]))
        self.assertEqual(out["passing_ids"], set())

    def test_id_duplicated_elsewhere_in_freeze_fails(self):
        month = hdx([["1", "A", 3.0, "SO", "2026-06"]])
        freeze = pd.concat([month, hdx([["1", "B", 2.0, "SO", "2025-10"]])])
        out = self.run_checks(fdw([["1", "A", 3.0, "SO", "2026-06-01"]]), month, freeze)
        self.assertEqual(out["passing_ids"], set())

    def test_mismatches_fail(self):
        good = ["1", "A", 3.0, "SO", "2026-06"]
        for bad_fdw in (["1", "Z", 3.0, "SO", "2026-06-01"],   # fnid
                        ["1", "A", 4.0, "SO", "2026-06-01"],   # value
                        ["1", "A", 3.0, "KE", "2026-06-01"],   # country
                        ["1", "A", 3.0, "SO", "2026-02-01"]):  # month
            out = self.run_checks(fdw([bad_fdw]), hdx([good]))
            self.assertEqual(out["passing_ids"], set(), bad_fdw)

    def test_unjoined_records_fail(self):
        out = self.run_checks(fdw([["2", "A", 3.0, "SO", "2026-06-01"]]),
                              hdx([["1", "A", 3.0, "SO", "2026-06"]]))
        self.assertEqual(out["passing_ids"], set())
        self.assertEqual(out["join"], {"both": 0, "left_only": 1, "right_only": 1})


def pair(code, uid, fnid, reciprocal, phase=3.0, ok=True, cov_area=None):
    return {"admin_code": code, "ISO": "SO", "id": uid, "fnid": fnid, "unit_type": "fsc_admin",
            "unit_full_name": f"unit {fnid}", "phase": phase, "record_checks_pass": ok,
            "intersection_m2": 1.0, "cov_area": cov_area or reciprocal,
            "cov_unit": reciprocal, "reciprocal": reciprocal}


class StrictMatches(unittest.TestCase):
    def test_competing_equivalent_units_rejected(self):
        pairs = pd.DataFrame([pair("1", "a", "A", 1.0), pair("1", "b", "B", 0.9999995)])
        self.assertTrue(strict_matches(pairs).empty)

    def test_unit_equivalent_to_two_areas_rejected(self):
        pairs = pd.DataFrame([pair("1", "a", "A", 1.0), pair("2", "a", "A", 1.0)])
        self.assertTrue(strict_matches(pairs).empty)

    def test_below_tolerance_or_failed_record_rejected(self):
        pairs = pd.DataFrame([pair("1", "a", "A", 0.99999), pair("2", "b", "B", 1.0, ok=False)])
        self.assertTrue(strict_matches(pairs).empty)

    def test_unique_equivalence_accepted(self):
        pairs = pd.DataFrame([pair("1", "a", "A", 1.0), pair("1", "c", "C", 1e-3, cov_area=1e-7)])
        self.assertEqual(list(strict_matches(pairs).index), ["1"])


class DecisionMain(unittest.TestCase):
    def test_missing_phase_stays_missing_and_fill_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            gpd.GeoDataFrame({"admin_code": ["1", "2", "3"], "unit_name": ["u1", "u2", "u3"],
                              "ISO": ["SO"] * 3},
                             geometry=[box(0, 0, 1, 1)] * 3, crs=6933).to_parquet(tmp / "p.parquet")
            pd.DataFrame({"FEWSNET_admin_code": ["1", "2", "3"], "date": ["2025-10-01"] * 3,
                          "fews_ipc": [3.0, 1.0, 1.0]}).to_parquet(tmp / "labels.parquet")
            pd.DataFrame({"admin_code": [1.0], "fews_ipc": [3.0], "year": [2025.0],
                          "month": [10.0]}).to_csv(tmp / "f25.csv", index=False)
            vintage = [pair("1", "a", "A", 1.0), pair("2", "b", "B", 1.0), pair("3", "c", "C", 1.0)]
            pd.DataFrame(vintage).to_parquet(tmp / "overlap_pairs_2021-06.parquet")
            month = [pair("1", "a", "A", 1.0, phase=3.0), pair("2", "b", "B", 1.0, phase=float("nan")),
                     pair("3", "c", "C", 1.0, phase=2.0)]
            for m in crosswalk_decide.TARGETS:
                pd.DataFrame(month).to_parquet(tmp / f"overlap_pairs_{m}.parquet")
            sys.argv = ["x", "--pairs", str(tmp), "--labels", str(tmp / "labels.parquet"),
                        "--fews2025", str(tmp / "f25.csv"), "--production",
                        str(tmp / "p.parquet"), "--out", str(tmp / "out")]
            crosswalk_decide.main()
            out = pd.read_csv(tmp / "out/strict_crosswalk_decisions.csv", dtype={"admin_code": str})
            out = out[out["month"] == "2025-10"].set_index("admin_code")
            self.assertTrue(pd.isna(out.loc["2", "accepted_phase"]))
            self.assertEqual(out.loc["2", "gap_reason"], "equivalent_unit_phase_missing_or_invalid")
            self.assertEqual(out.loc["1", "production_label_source"], "source_FEWS_2025")
            self.assertEqual(out.loc["2", "production_label_source"], "imputed_fill_proven")
            self.assertEqual(out.loc["3", "comparison"], "replaces_proven_imputed_fill")


if __name__ == "__main__":
    unittest.main()
