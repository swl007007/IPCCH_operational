import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "Final_harmonise" / "00_build_monthly_ipcch_base_input.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "build_monthly_ipcch_base_input", str(SCRIPT_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


class MonthlyIPCCHBaseInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.scaffold = self.root / "ipcch_scaffold_202604.csv"
        self.future_scaffold = self.root / "ipcch_scaffold_202605.csv"
        self.fixed = self.root / "fixed.csv"
        self.panel = self.root / "panel.csv"
        self.output = self.root / "ipcch_monthly_base_input_202604.csv"
        self.summary = self.root / "ipcch_monthly_base_input_202604_summary.json"
        self.future_output = self.root / "ipcch_monthly_base_input_202605.csv"
        self.future_summary = self.root / "ipcch_monthly_base_input_202605_summary.json"

        write_csv(
            self.scaffold,
            ["admin_code", "lat", "lon", "year", "month"],
            [
                {
                    "admin_code": "101.0",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "4",
                },
                {
                    "admin_code": "102",
                    "lat": "1.2",
                    "lon": "31.2",
                    "year": "2026",
                    "month": "4",
                },
            ],
        )
        write_csv(
            self.future_scaffold,
            ["admin_code", "lat", "lon", "year", "month"],
            [
                {
                    "admin_code": "101.0",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "5",
                }
            ],
        )
        write_csv(
            self.fixed,
            ["area_id", "admin_code", "lat", "lon", "crop", "elevation"],
            [
                {
                    "area_id": "101",
                    "admin_code": "101",
                    "lat": "1.1",
                    "lon": "31.1",
                    "crop": "1",
                    "elevation": "500",
                },
                {
                    "area_id": "102",
                    "admin_code": "102",
                    "lat": "1.2",
                    "lon": "31.2",
                    "crop": "0",
                    "elevation": "750",
                },
            ],
        )
        write_csv(
            self.panel,
            [
                "admin_code",
                "lat",
                "lon",
                "year",
                "month",
                "overall_phase",
                "EVI_mean",
                "Rainf_f_tavg_mean",
                "EVI_mean__l12",
            ],
            [
                {
                    "admin_code": "101",
                    "lat": "9.9",
                    "lon": "99.9",
                    "year": "2026",
                    "month": "4",
                    "overall_phase": "3",
                    "EVI_mean": "0.23",
                    "Rainf_f_tavg_mean": "12",
                    "EVI_mean__l12": "0.20",
                },
                {
                    "admin_code": "102",
                    "lat": "8.8",
                    "lon": "88.8",
                    "year": "2026",
                    "month": "4",
                    "overall_phase": "2",
                    "EVI_mean": "0.44",
                    "Rainf_f_tavg_mean": "15",
                    "EVI_mean__l12": "0.39",
                },
                {
                    "admin_code": "101",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "3",
                    "overall_phase": "1",
                    "EVI_mean": "0.11",
                    "Rainf_f_tavg_mean": "7",
                    "EVI_mean__l12": "0.08",
                },
            ],
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_builds_base_input_for_observed_month(self):
        module = load_module()

        result = module.build_monthly_base_input(
            year=2026,
            month=4,
            scaffold_path=self.scaffold,
            fixed_slow_path=self.fixed,
            historical_panel_path=self.panel,
            output_path=self.output,
            summary_path=self.summary,
        )

        rows = read_csv(self.output)
        self.assertEqual(2, len(rows))
        self.assertEqual(
            ["area_id", "admin_code", "lat", "lon", "year", "month"],
            list(rows[0].keys())[:6],
        )
        self.assertEqual("101", rows[0]["area_id"])
        self.assertEqual("101.0", rows[0]["admin_code"])
        self.assertEqual("1", rows[0]["crop"])
        self.assertEqual("500", rows[0]["elevation"])
        self.assertEqual("3", rows[0]["overall_phase"])
        self.assertEqual("0.23", rows[0]["EVI_mean"])
        self.assertNotIn("EVI_mean__l12", rows[0])

        with self.summary.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertEqual(result["row_count"], summary["row_count"])
        self.assertEqual(2, summary["fixed_slow_join"]["matched_rows"])
        self.assertEqual(0, summary["fixed_slow_join"]["unmatched_rows"])
        self.assertEqual(2, summary["source_join"]["matched_rows"])
        self.assertEqual(0, summary["source_join"]["unmatched_rows"])
        self.assertTrue(summary["source_join"]["target_month_present_in_source"])

    def test_future_month_keeps_scaffold_and_fixed_features(self):
        module = load_module()

        module.build_monthly_base_input(
            year=2026,
            month=5,
            scaffold_path=self.future_scaffold,
            fixed_slow_path=self.fixed,
            historical_panel_path=self.panel,
            output_path=self.future_output,
            summary_path=self.future_summary,
        )

        rows = read_csv(self.future_output)
        self.assertEqual(1, len(rows))
        self.assertEqual("101", rows[0]["area_id"])
        self.assertEqual("1", rows[0]["crop"])
        self.assertEqual("", rows[0]["EVI_mean"])

        with self.future_summary.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        self.assertFalse(summary["source_join"]["target_month_present_in_source"])
        self.assertEqual(0, summary["source_join"]["matched_rows"])
        self.assertEqual(1, summary["source_join"]["unmatched_rows"])

    def test_duplicate_scaffold_key_fails(self):
        module = load_module()
        duplicate_scaffold = self.root / "duplicate_scaffold.csv"
        write_csv(
            duplicate_scaffold,
            ["admin_code", "lat", "lon", "year", "month"],
            [
                {
                    "admin_code": "101",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "4",
                },
                {
                    "admin_code": "101.0",
                    "lat": "1.1",
                    "lon": "31.1",
                    "year": "2026",
                    "month": "4",
                },
            ],
        )

        with self.assertRaises(SystemExit) as raised:
            module.build_monthly_base_input(
                year=2026,
                month=4,
                scaffold_path=duplicate_scaffold,
                fixed_slow_path=self.fixed,
                historical_panel_path=self.panel,
                output_path=self.output,
                summary_path=self.summary,
            )
        self.assertIn("Duplicate scaffold keys", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
