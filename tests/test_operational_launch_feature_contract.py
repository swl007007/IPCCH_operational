import tempfile
import unittest
from pathlib import Path

import pandas as pd

from model_pipeline.ipcch_launch_runtime.feature_contract import (
    FeatureContractError,
    apply_feature_contract,
)


class OperationalLaunchFeatureContractTests(unittest.TestCase):
    def test_builds_matrix_from_required_static_join_and_median_impute_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)
            lookup_path = package_root / "lookups" / "static.csv"
            lookup_path.parent.mkdir()
            pd.DataFrame(
                {
                    "area_id": ["A", "B"],
                    "static_value": [10.0, 20.0],
                }
            ).to_csv(lookup_path, index=False)

            monthly_input = pd.DataFrame(
                {
                    "area_id": ["A", "B"],
                    "required_src": ["1.5", "2.5"],
                    "impute_src": [pd.NA, 8.0],
                }
            )
            contract = pd.DataFrame(
                [
                    self._contract_row(
                        "required_feature",
                        "required_src",
                        category="required",
                        dtype="float",
                    ),
                    self._contract_row(
                        "static_feature",
                        "static_value",
                        category="static_join",
                        lookup_asset="lookups/static.csv",
                        dtype="float",
                    ),
                    self._contract_row(
                        "imputed_feature",
                        "impute_src",
                        category="median_impute",
                        fill_value_or_stat_key="imputed_feature_median",
                        dtype="float",
                    ),
                ]
            )

            matrix, report = apply_feature_contract(
                monthly_input,
                contract,
                ["static_feature", "required_feature", "imputed_feature"],
                package_root=package_root,
                metadata={"imputation_statistics": {"imputed_feature_median": 6.5}},
            )

        self.assertEqual(
            ["static_feature", "required_feature", "imputed_feature"],
            list(matrix.columns),
        )
        self.assertEqual([10.0, 20.0], matrix["static_feature"].tolist())
        self.assertEqual([1.5, 2.5], matrix["required_feature"].tolist())
        self.assertEqual([6.5, 8.0], matrix["imputed_feature"].tolist())
        self.assertEqual("passed", report["status"])
        self.assertEqual(3, report["feature_count"])
        self.assertEqual(["static_feature", "imputed_feature"], report["filled_features"])
        self.assertEqual([], report["ignored_contract_features"])
        self.assertEqual([], report["warnings"])
        self.assertEqual("static_join", report["features"]["static_feature"]["fill_method"])

    def test_missing_required_source_column_fails(self):
        monthly_input = pd.DataFrame({"area_id": ["A"]})
        contract = pd.DataFrame(
            [self._contract_row("required_feature", "required_src", category="required")]
        )

        with self.assertRaisesRegex(FeatureContractError, "required_src"):
            apply_feature_contract(
                monthly_input,
                contract,
                ["required_feature"],
                package_root=Path("."),
                metadata={},
            )

    def test_missing_model_feature_in_contract_fails(self):
        monthly_input = pd.DataFrame({"area_id": ["A"], "present_src": [1]})
        contract = pd.DataFrame(
            [self._contract_row("present_feature", "present_src", category="required")]
        )

        with self.assertRaisesRegex(FeatureContractError, "Missing.*absent_feature"):
            apply_feature_contract(
                monthly_input,
                contract,
                ["present_feature", "absent_feature"],
                package_root=Path("."),
                metadata={},
            )

    def test_unsupported_or_excluded_model_feature_fails(self):
        monthly_input = pd.DataFrame({"area_id": ["A"], "legacy_src": [1]})
        contract = pd.DataFrame(
            [
                self._contract_row(
                    "legacy_feature",
                    "legacy_src",
                    category="required",
                    supported=False,
                )
            ]
        )

        with self.assertRaisesRegex(FeatureContractError, "unsupported or excluded"):
            apply_feature_contract(
                monthly_input,
                contract,
                ["legacy_feature"],
                package_root=Path("."),
                metadata={},
            )

    def test_duplicate_contract_feature_row_fails(self):
        monthly_input = pd.DataFrame({"area_id": ["A"], "src": [1]})
        contract = pd.DataFrame(
            [
                self._contract_row("feature", "src", category="required"),
                self._contract_row("feature", "src", category="required"),
            ]
        )

        with self.assertRaisesRegex(FeatureContractError, "Duplicate.*feature"):
            apply_feature_contract(
                monthly_input,
                contract,
                ["feature"],
                package_root=Path("."),
                metadata={},
            )

    def test_static_lookup_duplicate_area_id_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)
            lookup_path = package_root / "lookup.csv"
            pd.DataFrame(
                {"area_id": ["A", "A"], "static_value": [1, 2]}
            ).to_csv(lookup_path, index=False)
            monthly_input = pd.DataFrame({"area_id": ["A"]})
            contract = pd.DataFrame(
                [
                    self._contract_row(
                        "static_feature",
                        "static_value",
                        category="static_join",
                        lookup_asset="lookup.csv",
                    )
                ]
            )

            with self.assertRaisesRegex(FeatureContractError, "duplicate.*area_id"):
                apply_feature_contract(
                    monthly_input,
                    contract,
                    ["static_feature"],
                    package_root=package_root,
                    metadata={},
                )

    def test_static_lookup_missing_joined_values_beyond_tolerance_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)
            lookup_path = package_root / "lookup.csv"
            pd.DataFrame({"area_id": ["A"], "static_value": [1]}).to_csv(
                lookup_path, index=False
            )
            monthly_input = pd.DataFrame({"area_id": ["A", "B"]})
            contract = pd.DataFrame(
                [
                    self._contract_row(
                        "static_feature",
                        "static_value",
                        category="static_join",
                        lookup_asset="lookup.csv",
                        missing_tolerance=0.0,
                    )
                ]
            )

            with self.assertRaisesRegex(FeatureContractError, "static_feature.*missing"):
                apply_feature_contract(
                    monthly_input,
                    contract,
                    ["static_feature"],
                    package_root=package_root,
                    metadata={},
                )

    def test_carry_forward_lookup_works_and_reports_fill(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            package_root = Path(tmpdir)
            lookup_path = package_root / "lookup.csv"
            pd.DataFrame({"area_id": ["A", "B"], "carry_value": [3, 4]}).to_csv(
                lookup_path, index=False
            )
            monthly_input = pd.DataFrame({"area_id": ["A", "B"]})
            contract = pd.DataFrame(
                [
                    self._contract_row(
                        "carry_feature",
                        "carry_value",
                        category="carry_forward",
                        lookup_asset="lookup.csv",
                        dtype="integer",
                    )
                ]
            )

            matrix, report = apply_feature_contract(
                monthly_input,
                contract,
                ["carry_feature"],
                package_root=package_root,
                metadata={},
            )

        self.assertEqual([3, 4], matrix["carry_feature"].tolist())
        self.assertEqual(["carry_feature"], report["filled_features"])
        self.assertEqual("carry forward", report["features"]["carry_feature"]["fill_method"])

    def test_median_impute_fills_partial_missing_values_from_metadata(self):
        monthly_input = pd.DataFrame({"area_id": ["A", "B"], "feature_src": [1.0, pd.NA]})
        contract = pd.DataFrame(
            [
                self._contract_row(
                    "feature",
                    "feature_src",
                    category="median_impute",
                    fill_value_or_stat_key="feature_median",
                    dtype="float",
                )
            ]
        )

        matrix, report = apply_feature_contract(
            monthly_input,
            contract,
            ["feature"],
            package_root=Path("."),
            metadata={"imputation_statistics": {"feature_median": 9.0}},
        )

        self.assertEqual([1.0, 9.0], matrix["feature"].tolist())
        self.assertEqual(["feature"], report["filled_features"])
        self.assertEqual(0.5, report["features"]["feature"]["pre_fill_missing_rate"])
        self.assertEqual(0.0, report["features"]["feature"]["post_fill_missing_rate"])

    def test_invalid_nonmissing_float_text_fails_even_with_missing_tolerance(self):
        monthly_input = pd.DataFrame({"area_id": ["A", "B"], "feature_src": ["1.0", "bad"]})
        contract = pd.DataFrame(
            [
                self._contract_row(
                    "feature",
                    "feature_src",
                    category="required",
                    dtype="float",
                    missing_tolerance=1.0,
                )
            ]
        )

        with self.assertRaisesRegex(FeatureContractError, "feature.*numeric.*bad"):
            apply_feature_contract(
                monthly_input,
                contract,
                ["feature"],
                package_root=Path("."),
                metadata={},
            )

    def test_invalid_nonmissing_integer_text_fails_even_with_missing_tolerance(self):
        monthly_input = pd.DataFrame({"area_id": ["A", "B"], "feature_src": ["1", "bad"]})
        contract = pd.DataFrame(
            [
                self._contract_row(
                    "feature",
                    "feature_src",
                    category="required",
                    dtype="integer",
                    missing_tolerance=1.0,
                )
            ]
        )

        with self.assertRaisesRegex(FeatureContractError, "feature.*numeric.*bad"):
            apply_feature_contract(
                monthly_input,
                contract,
                ["feature"],
                package_root=Path("."),
                metadata={},
            )

    def test_valid_nullable_numeric_values_are_preserved(self):
        monthly_input = pd.DataFrame(
            {
                "area_id": ["A", "B"],
                "float_src": ["1.25", pd.NA],
                "integer_src": ["2", pd.NA],
            }
        )
        contract = pd.DataFrame(
            [
                self._contract_row(
                    "float_feature",
                    "float_src",
                    category="required",
                    dtype="float",
                    missing_tolerance=0.5,
                ),
                self._contract_row(
                    "integer_feature",
                    "integer_src",
                    category="required",
                    dtype="integer",
                    missing_tolerance=0.5,
                ),
            ]
        )

        matrix, report = apply_feature_contract(
            monthly_input,
            contract,
            ["float_feature", "integer_feature"],
            package_root=Path("."),
            metadata={},
        )

        self.assertEqual(1.25, matrix.loc[0, "float_feature"])
        self.assertTrue(pd.isna(matrix.loc[1, "float_feature"]))
        self.assertEqual(2, matrix.loc[0, "integer_feature"])
        self.assertTrue(pd.isna(matrix.loc[1, "integer_feature"]))
        self.assertEqual(0.5, report["features"]["float_feature"]["missing_rate"])
        self.assertEqual(0.5, report["features"]["integer_feature"]["missing_rate"])

    def test_boolean_and_categorical_coercion_are_deterministic(self):
        monthly_input = pd.DataFrame(
            {
                "area_id": ["A", "B"],
                "bool_src": ["yes", "0"],
                "category_src": ["Phase 3", "Phase 4"],
            }
        )
        contract = pd.DataFrame(
            [
                self._contract_row(
                    "bool_feature",
                    "bool_src",
                    category="required",
                    dtype="boolean",
                ),
                self._contract_row(
                    "category_feature",
                    "category_src",
                    category="required",
                    dtype="categorical",
                ),
            ]
        )

        matrix, report = apply_feature_contract(
            monthly_input,
            contract,
            ["bool_feature", "category_feature"],
            package_root=Path("."),
            metadata={},
        )

        self.assertEqual([True, False], matrix["bool_feature"].tolist())
        self.assertEqual(["Phase 3", "Phase 4"], matrix["category_feature"].tolist())
        self.assertEqual("boolean", report["features"]["bool_feature"]["dtype"])
        self.assertEqual("categorical", report["features"]["category_feature"]["dtype"])

    def test_derived_feature_fails_clearly(self):
        monthly_input = pd.DataFrame({"area_id": ["A"], "src": [1]})
        contract = pd.DataFrame(
            [self._contract_row("derived_feature", "src", category="derived")]
        )

        with self.assertRaisesRegex(FeatureContractError, "Derived.*not supported"):
            apply_feature_contract(
                monthly_input,
                contract,
                ["derived_feature"],
                package_root=Path("."),
                metadata={},
            )

    def test_extra_contract_feature_is_ignored_and_reported(self):
        monthly_input = pd.DataFrame({"area_id": ["A"], "src": [1], "extra_src": [2]})
        contract = pd.DataFrame(
            [
                self._contract_row("model_feature", "src", category="required"),
                self._contract_row("extra_feature", "extra_src", category="required"),
            ]
        )

        matrix, report = apply_feature_contract(
            monthly_input,
            contract,
            ["model_feature"],
            package_root=Path("."),
            metadata={},
        )

        self.assertEqual(["model_feature"], list(matrix.columns))
        self.assertEqual(["extra_feature"], report["ignored_contract_features"])

    def _contract_row(
        self,
        feature_name,
        source_column,
        *,
        category,
        dtype="float",
        required_in_input=None,
        fill_value_or_stat_key="",
        lookup_asset="",
        missing_tolerance=0.0,
        supported=True,
    ):
        if required_in_input is None:
            required_in_input = category == "required"
        return {
            "model_feature": feature_name,
            "source_column": source_column,
            "category": category,
            "dtype": dtype,
            "required_in_input": required_in_input,
            "fill_value_or_stat_key": fill_value_or_stat_key,
            "lookup_asset": lookup_asset,
            "missing_tolerance": missing_tolerance,
            "supported": supported,
        }


if __name__ == "__main__":
    unittest.main()
