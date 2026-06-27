import tempfile
import unittest
from pathlib import Path

import pandas as pd

from tools.reshape_remote_sensing_wide_to_long import reshape_wide_table


class RemoteSensingWideToLongTests(unittest.TestCase):
    def test_maps_region_ids_and_yyyy_mm_columns_to_monthly_feature_rows(self):
        wide = pd.DataFrame(
            {
                "region_id": [10, 20],
                "2026_04": [1.5, 3.5],
                "2026_05": [2.5, 4.5],
            }
        )
        mapping = pd.DataFrame(
            {
                "region_id": [10, 20],
                "area_id": ["area-a", "area-b"],
            }
        )

        result = reshape_wide_table(wide, "EVI_mean", mapping_df=mapping)

        self.assertEqual(
            result.to_dict("records"),
            [
                {"area_id": "area-a", "year": 2026, "month": 4, "EVI_mean": 1.5},
                {"area_id": "area-a", "year": 2026, "month": 5, "EVI_mean": 2.5},
                {"area_id": "area-b", "year": 2026, "month": 4, "EVI_mean": 3.5},
                {"area_id": "area-b", "year": 2026, "month": 5, "EVI_mean": 4.5},
            ],
        )

    def test_parses_gosif_month_columns(self):
        wide = pd.DataFrame(
            {
                "region_id": [101],
                "2026.M04": [9.25],
            }
        )

        result = reshape_wide_table(wide, "GPP_mean")

        self.assertEqual(
            result.to_dict("records"),
            [{"area_id": 101, "year": 2026, "month": 4, "GPP_mean": 9.25}],
        )

    def test_pivots_fldas_band_columns_to_monthly_band_features(self):
        wide = pd.DataFrame(
            {
                "region_id": [101],
                "2026_04_B1": [11.0],
                "2026_04_B2": [22.0],
                "2026_05_B1": [33.0],
            }
        )

        result = reshape_wide_table(wide, "fldas_mean")

        self.assertEqual(
            result.to_dict("records"),
            [
                {
                    "area_id": 101,
                    "year": 2026,
                    "month": 4,
                    "fldas_mean_B1": 11.0,
                    "fldas_mean_B2": 22.0,
                },
                {
                    "area_id": 101,
                    "year": 2026,
                    "month": 5,
                    "fldas_mean_B1": 33.0,
                    "fldas_mean_B2": None,
                },
            ],
        )

    def test_cli_writes_monthly_table(self):
        from tools.reshape_remote_sensing_wide_to_long import main

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_csv = tmp / "wide.csv"
            output_csv = tmp / "long.csv"
            pd.DataFrame(
                {
                    "region_id": [7],
                    "2026_04": [8.0],
                }
            ).to_csv(input_csv, index=False)

            main(
                [
                    "--input-csv",
                    str(input_csv),
                    "--output-csv",
                    str(output_csv),
                    "--feature-name",
                    "nightlight_mean",
                ]
            )

            written = pd.read_csv(output_csv)
            self.assertEqual(
                written.to_dict("records"),
                [{"area_id": 7, "year": 2026, "month": 4, "nightlight_mean": 8.0}],
            )

    def test_duplicate_mapping_fails(self):
        wide = pd.DataFrame({"region_id": [10], "2026_04": [1.5]})
        mapping = pd.DataFrame({"region_id": [10, 10], "area_id": ["a", "b"]})

        with self.assertRaisesRegex(ValueError, "Duplicate mapping"):
            reshape_wide_table(wide, "EVI_mean", mapping_df=mapping)


if __name__ == "__main__":
    unittest.main()
