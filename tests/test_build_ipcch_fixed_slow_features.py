import csv
import inspect
import importlib.util
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "tools" / "build_ipcch_fixed_slow_features.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "build_ipcch_fixed_slow_features", str(SCRIPT_PATH)
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


class FixedSlowFeatureBuilderTests(unittest.TestCase):
    def test_adds_coastline_distance_by_lat_lon(self):
        module = load_module()
        if "coastline_source" not in inspect.signature(module.build_assets).parameters:
            self.fail("build_assets should accept a coastline_source input")

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "panel.csv"
            coastline = root / "coastline.csv"
            output = root / "fixed.csv"
            summary = root / "summary.csv"

            write_csv(
                source,
                [
                    "admin_code",
                    "lat",
                    "lon",
                    "ISO3",
                    "country",
                    "country_code",
                    "country_en",
                    "state",
                    "year",
                    "month",
                    "AEZ_4000",
                    "crop",
                ],
                [
                    {
                        "admin_code": "10",
                        "lat": "1.123456789012",
                        "lon": "31.123456789012",
                        "ISO3": "AAA",
                        "country": "A",
                        "country_code": "AA",
                        "country_en": "A",
                        "state": "A1",
                        "year": "2026",
                        "month": "4",
                        "AEZ_4000": "1",
                        "crop": "25",
                    },
                    {
                        "admin_code": "11",
                        "lat": "2.200000000000",
                        "lon": "32.200000000000",
                        "ISO3": "BBB",
                        "country": "B",
                        "country_code": "BB",
                        "country_en": "B",
                        "state": "B1",
                        "year": "2026",
                        "month": "4",
                        "AEZ_4000": "0",
                        "crop": "40",
                    },
                ],
            )
            write_csv(
                coastline,
                ["lat", "lon", "coastline_dist"],
                [
                    {
                        "lat": "1.1234567890123",
                        "lon": "31.1234567890123",
                        "coastline_dist": "-7.0",
                    },
                    {
                        "lat": "2.2000000000004",
                        "lon": "32.2000000000004",
                        "coastline_dist": "44.5",
                    },
                ],
            )

            module.build_assets(
                str(source),
                str(output),
                str(summary),
                coastline_source=str(coastline),
            )

            fixed_rows = read_csv(output)
            self.assertEqual("-7.0", fixed_rows[0]["coastline_dist"])
            self.assertEqual("44.5", fixed_rows[1]["coastline_dist"])

            summary_rows = {
                row["feature"]: row
                for row in read_csv(summary)
            }
            self.assertEqual("coastline_distance", summary_rows["coastline_dist"]["family"])
            self.assertEqual("2", summary_rows["coastline_dist"]["areas_with_value"])
            self.assertEqual("0", summary_rows["coastline_dist"]["missing_area_count"])


if __name__ == "__main__":
    unittest.main()
