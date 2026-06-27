import unittest

import pandas as pd

from model_pipeline.ipcch_launch_runtime.adapters import (
    InputContractError,
    validate_monthly_input,
)


class OperationalLaunchInputContractTests(unittest.TestCase):
    def test_valid_admin_code_only_input_creates_area_id_and_preserves_leading_zeros(
        self,
    ):
        source = pd.DataFrame(
            {
                "admin_code": ["00123", "00456"],
                "year": [2026, 2026],
                "month": [4, 4],
                "feature": [1.5, 2.5],
            }
        )

        validated, report = validate_monthly_input(source, feature_month="2026-04")

        self.assertEqual(["00123", "00456"], validated["area_id"].tolist())
        self.assertEqual(["00123", "00456"], validated["admin_code"].tolist())
        self.assertEqual([0, 1], validated["_row_id"].tolist())
        self.assertEqual([1.5, 2.5], validated["feature"].tolist())
        self.assertEqual("passed", report["status"])
        self.assertEqual("2026-04", report["feature_month"])
        self.assertEqual(2, report["row_count"])
        self.assertEqual(2, report["unique_area_count"])
        self.assertEqual(
            ["admin_code", "year", "month", "feature"], report["input_columns"]
        )
        self.assertEqual(2, report["coverage"]["area_id_nonmissing"])

    def test_id_whitespace_is_trimmed_while_preserving_leading_zeros(self):
        source = pd.DataFrame(
            {
                "admin_code": [" 001 ", "\t0002\n"],
                "year": [2026, 2026],
                "month": [4, 4],
            }
        )

        validated, report = validate_monthly_input(source, feature_month="202604")

        self.assertEqual(["001", "0002"], validated["admin_code"].tolist())
        self.assertEqual(["001", "0002"], validated["area_id"].tolist())
        self.assertEqual("passed", report["status"])
        self.assertEqual("2026-04", report["feature_month"])

    def test_feature_month_mismatch_fails(self):
        source = pd.DataFrame(
            {"area_id": ["1"], "year": [2026], "month": [4], "feature": [1]}
        )

        with self.assertRaisesRegex(InputContractError, "feature_month"):
            validate_monthly_input(source, feature_month="2026-05")

    def test_duplicate_area_id_fails(self):
        source = pd.DataFrame(
            {
                "area_id": ["1", "1"],
                "year": [2026, 2026],
                "month": [4, 4],
            }
        )

        with self.assertRaisesRegex(InputContractError, "Duplicate area_id"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_duplicate_area_id_after_trim_fails(self):
        source = pd.DataFrame(
            {
                "area_id": ["001", " 001 "],
                "year": [2026, 2026],
                "month": [4, 4],
            }
        )

        with self.assertRaisesRegex(InputContractError, "Duplicate area_id"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_both_area_id_and_admin_code_inconsistent_fails(self):
        source = pd.DataFrame(
            {
                "area_id": ["001", "002"],
                "admin_code": ["001", "999"],
                "year": [2026, 2026],
                "month": [4, 4],
            }
        )

        with self.assertRaisesRegex(InputContractError, "area_id/admin_code"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_multiple_months_in_one_input_fails(self):
        source = pd.DataFrame(
            {
                "area_id": ["1", "2"],
                "year": [2026, 2026],
                "month": [4, 5],
            }
        )

        with self.assertRaisesRegex(InputContractError, "exactly one feature month"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_invalid_input_month_range_fails(self):
        source = pd.DataFrame(
            {
                "area_id": ["1"],
                "year": [2026],
                "month": [13],
            }
        )

        with self.assertRaisesRegex(
            InputContractError, "month must be between 1 and 12"
        ):
            validate_monthly_input(source, feature_month="2026-04")

    def test_missing_year_column_fails(self):
        source = pd.DataFrame(
            {
                "area_id": ["1"],
                "month": [4],
            }
        )

        with self.assertRaisesRegex(InputContractError, "year"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_missing_month_column_fails(self):
        source = pd.DataFrame(
            {
                "area_id": ["1"],
                "year": [2026],
            }
        )

        with self.assertRaisesRegex(InputContractError, "month"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_missing_both_id_columns_fails(self):
        source = pd.DataFrame(
            {
                "year": [2026],
                "month": [4],
                "feature": [1],
            }
        )

        with self.assertRaisesRegex(InputContractError, "area_id or admin_code"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_column_names_are_case_sensitive(self):
        source = pd.DataFrame(
            {
                "Admin_Code": ["001"],
                "year": [2026],
                "month": [4],
            }
        )

        with self.assertRaisesRegex(InputContractError, "area_id or admin_code"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_existing_row_id_column_fails_as_reserved_runtime_field(self):
        source = pd.DataFrame(
            {
                "_row_id": ["upstream"],
                "admin_code": ["001"],
                "year": [2026],
                "month": [4],
            }
        )

        with self.assertRaisesRegex(InputContractError, "_row_id"):
            validate_monthly_input(source, feature_month="2026-04")

    def test_null_tokens_normalize_to_pandas_na_without_breaking_unrelated_columns(
        self,
    ):
        source = pd.DataFrame(
            {
                "admin_code": ["001", "002"],
                "year": [2026, 2026],
                "month": [4, 4],
                "note": ["NULL", "observed"],
                "score": ["", "5"],
            }
        )

        validated, report = validate_monthly_input(source, feature_month="2026-04")

        self.assertTrue(pd.isna(validated.loc[0, "note"]))
        self.assertEqual("observed", validated.loc[1, "note"])
        self.assertTrue(pd.isna(validated.loc[0, "score"]))
        self.assertEqual("5", validated.loc[1, "score"])
        self.assertEqual(1, report["coverage"]["null_counts"]["note"])
        self.assertEqual(1, report["coverage"]["null_counts"]["score"])


if __name__ == "__main__":
    unittest.main()
