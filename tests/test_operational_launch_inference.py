import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

import pandas as pd

from model_pipeline.ipcch_launch_runtime.inference import InferenceError, score_scope
from model_pipeline.ipcch_launch_runtime.model_package import (
    ModelPackageError,
    load_scope_package,
)


class ConstantModel:
    def __init__(self, values):
        self.values = values

    def predict(self, feature_matrix):
        if callable(self.values):
            return self.values(feature_matrix)
        if isinstance(self.values, list):
            return self.values
        return [self.values] * len(feature_matrix)


class OperationalLaunchInferenceTests(unittest.TestCase):
    def test_constant_models_score_threshold_and_decode_phase(self):
        monthly_rows = pd.DataFrame(
            {
                "area_id": ["A", "B", "C"],
                "admin_code": ["AA", "BB", "CC"],
            }
        )
        feature_matrix = pd.DataFrame({"feature": [1.0, 2.0, 3.0]})
        models = {
            "phase2_worse": ConstantModel([0.8, 0.8, 0.8]),
            "phase3_worse": ConstantModel([0.7, 0.7, 0.1]),
            "phase4_worse": ConstantModel([0.6, 0.1, 0.1]),
            "phase5_worse": ConstantModel([0.1, 0.1, 0.1]),
        }

        scored, summary = score_scope(
            monthly_rows=monthly_rows,
            feature_matrix=feature_matrix,
            models=models,
            thresholds={"default": 0.5},
            scope_months=3,
            feature_month="2026-04",
            target_month="2026-07",
            model_package_id="pkg-001",
            source_input="input.csv",
            monotonicity_policy="fail",
        )

        self.assertEqual(["A", "B", "C"], scored["area_id"].tolist())
        self.assertEqual(["AA", "BB", "CC"], scored["admin_code"].tolist())
        self.assertEqual([4, 3, 2], scored["overall_phase_pred"].tolist())
        self.assertEqual([1, 1, 1], scored["phase2_worse_pred"].tolist())
        self.assertEqual([1, 1, 0], scored["phase3_worse_pred"].tolist())
        self.assertEqual([1, 0, 0], scored["phase4_worse_pred"].tolist())
        self.assertEqual([0, 0, 0], scored["phase5_worse_pred"].tolist())
        self.assertEqual("2026-04", scored["feature_period"].iloc[0])
        self.assertEqual("2026-07", scored["target_period"].iloc[0])
        self.assertEqual(3, scored["scope_months"].iloc[0])
        self.assertEqual("pkg-001", scored["model_package_id"].iloc[0])
        self.assertEqual("input.csv", scored["source_input"].iloc[0])
        self.assertEqual("passed", summary["status"])
        self.assertEqual(3, summary["row_count"])
        self.assertEqual(3, summary["scope_months"])
        self.assertEqual("2026-04", summary["feature_month"])
        self.assertEqual("2026-07", summary["target_month"])
        self.assertEqual(
            {
                "phase2_worse": 0.5,
                "phase3_worse": 0.5,
                "phase4_worse": 0.5,
                "phase5_worse": 0.5,
            },
            summary["thresholds"],
        )
        self.assertEqual("fail", summary["monotonicity_policy"])
        self.assertEqual(
            [
                "phase2_worse_score",
                "phase3_worse_score",
                "phase4_worse_score",
                "phase5_worse_score",
            ],
            summary["score_columns"],
        )
        self.assertEqual(
            [
                "phase2_worse_pred",
                "phase3_worse_pred",
                "phase4_worse_pred",
                "phase5_worse_pred",
            ],
            summary["pred_columns"],
        )

    def test_missing_model_fails(self):
        models = {
            "phase2_worse": ConstantModel(0.8),
            "phase3_worse": ConstantModel(0.7),
            "phase4_worse": ConstantModel(0.1),
        }

        with self.assertRaisesRegex(InferenceError, "phase5_worse"):
            self._score(models=models)

    def test_non_finite_score_fails(self):
        models = self._models()
        models["phase3_worse"] = ConstantModel([0.4, float("nan")])

        with self.assertRaisesRegex(InferenceError, "finite"):
            self._score(models=models)

    def test_score_length_mismatch_fails(self):
        models = self._models()
        models["phase3_worse"] = ConstantModel(lambda feature_matrix: [0.8])

        with self.assertRaisesRegex(InferenceError, "length"):
            self._score(models=models)

    def test_non_monotonic_predictions_fail_under_fail_policy(self):
        models = {
            "phase2_worse": ConstantModel([0.1, 0.8]),
            "phase3_worse": ConstantModel([0.8, 0.8]),
            "phase4_worse": ConstantModel([0.1, 0.1]),
            "phase5_worse": ConstantModel([0.1, 0.1]),
        }

        with self.assertRaisesRegex(InferenceError, "Non-monotonic"):
            self._score(models=models, monotonicity_policy="fail")

    def test_non_monotonic_predictions_correct_under_cummax_policy(self):
        models = {
            "phase2_worse": ConstantModel([0.1, 0.8]),
            "phase3_worse": ConstantModel([0.8, 0.8]),
            "phase4_worse": ConstantModel([0.1, 0.1]),
            "phase5_worse": ConstantModel([0.1, 0.1]),
        }

        scored, summary = self._score(models=models, monotonicity_policy="cummax")

        self.assertEqual([1, 1], scored["phase2_worse_pred"].tolist())
        self.assertEqual([1, 1], scored["phase3_worse_pred"].tolist())
        self.assertEqual([0, 0], scored["phase4_worse_pred"].tolist())
        self.assertEqual([3, 3], scored["overall_phase_pred"].tolist())
        self.assertEqual("cummax", summary["monotonicity_policy"])

    def test_per_target_threshold_overrides_default(self):
        models = self._models(
            phase2=[0.8, 0.8],
            phase3=[0.4, 0.7],
            phase4=[0.1, 0.1],
            phase5=[0.1, 0.1],
        )

        scored, summary = self._score(
            models=models,
            thresholds={"default": 0.5, "phase3_worse": 0.3},
        )

        self.assertEqual([1, 1], scored["phase3_worse_pred"].tolist())
        self.assertEqual([3, 3], scored["overall_phase_pred"].tolist())
        self.assertEqual(0.3, summary["thresholds"]["phase3_worse"])

    def test_score_key_threshold_override_works(self):
        models = self._models(
            phase2=[0.8, 0.8],
            phase3=[0.4, 0.7],
            phase4=[0.1, 0.1],
            phase5=[0.1, 0.1],
        )

        scored, _summary = self._score(
            models=models,
            thresholds={"default": 0.5, "phase3_worse_score": 0.3},
        )

        self.assertEqual([1, 1], scored["phase3_worse_pred"].tolist())

    def test_row_id_is_preserved(self):
        monthly_rows = pd.DataFrame({"_row_id": [10, 11], "area_id": ["A", "B"]})

        scored, _summary = self._score(monthly_rows=monthly_rows)

        self.assertEqual([10, 11], scored["_row_id"].tolist())
        self.assertEqual(["A", "B"], scored["area_id"].tolist())

    def test_mismatched_monthly_and_feature_indexes_fail(self):
        monthly_rows = pd.DataFrame(
            {"area_id": ["A", "B"]},
            index=[100, 101],
        )
        feature_matrix = pd.DataFrame(
            {"feature": [1.0, 2.0]},
            index=[101, 100],
        )

        with self.assertRaisesRegex(InferenceError, "index"):
            self._score(monthly_rows=monthly_rows, feature_matrix=feature_matrix)

    def test_task2_shaped_package_loads_all_four_model_targets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scope_dir = Path(tmpdir) / "scope_3m"
            scope_dir.mkdir()
            (scope_dir / "feature_columns.json").write_text(
                json.dumps(["feature_a", "feature_b"]),
                encoding="utf-8",
            )
            (scope_dir / "feature_contract.csv").write_text(
                "model_feature,category\nfeature_a,required\n",
                encoding="utf-8",
            )
            (scope_dir / "model_metadata.json").write_text(
                json.dumps({"model_package_id": "pkg-001"}),
                encoding="utf-8",
            )
            for target in (
                "phase2_worse",
                "phase3_worse",
                "phase4_worse",
                "phase5_worse",
            ):
                (scope_dir / "{0}_model.json".format(target)).write_text(
                    "{}",
                    encoding="utf-8",
                )

            fake_module = types.SimpleNamespace()
            loaded_paths = []

            class FakeXGBRegressor:
                def load_model(self, path):
                    loaded_paths.append(Path(path).name)

            fake_module.XGBRegressor = FakeXGBRegressor
            original_xgboost = sys.modules.get("xgboost")
            sys.modules["xgboost"] = fake_module
            try:
                package = load_scope_package(Path(tmpdir), 3)
            finally:
                if original_xgboost is None:
                    sys.modules.pop("xgboost", None)
                else:
                    sys.modules["xgboost"] = original_xgboost

        self.assertEqual(["feature_a", "feature_b"], package["feature_columns"])
        self.assertEqual({"model_package_id": "pkg-001"}, package["metadata"])
        self.assertEqual(["feature_a"], package["contract"]["model_feature"].tolist())
        self.assertEqual(scope_dir, package["scope_dir"])
        self.assertEqual(
            {
                "phase2_worse",
                "phase3_worse",
                "phase4_worse",
                "phase5_worse",
            },
            set(package["models"]),
        )
        self.assertEqual(
            [
                "phase2_worse_model.json",
                "phase3_worse_model.json",
                "phase4_worse_model.json",
                "phase5_worse_model.json",
            ],
            loaded_paths,
        )

    def test_missing_package_model_file_fails_with_task2_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scope_dir = Path(tmpdir) / "scope_3m"
            scope_dir.mkdir()
            (scope_dir / "feature_columns.json").write_text(
                json.dumps(["feature"]),
                encoding="utf-8",
            )
            (scope_dir / "feature_contract.csv").write_text(
                "model_feature,category\nfeature,required\n",
                encoding="utf-8",
            )
            (scope_dir / "model_metadata.json").write_text(
                "{}",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ModelPackageError, "phase2_worse_model.json"):
                load_scope_package(Path(tmpdir), 3)

    def _score(
        self,
        *,
        monthly_rows=None,
        feature_matrix=None,
        models=None,
        thresholds=None,
        monotonicity_policy="fail",
    ):
        if monthly_rows is None:
            monthly_rows = pd.DataFrame({"area_id": ["A", "B"]})
        if feature_matrix is None:
            feature_matrix = pd.DataFrame(
                {"feature": [1.0, 2.0]},
                index=monthly_rows.index,
            )
        if models is None:
            models = self._models()
        if thresholds is None:
            thresholds = {"default": 0.5}
        return score_scope(
            monthly_rows=monthly_rows,
            feature_matrix=feature_matrix,
            models=models,
            thresholds=thresholds,
            scope_months=3,
            feature_month="2026-04",
            target_month="2026-07",
            model_package_id="pkg-001",
            source_input="input.csv",
            monotonicity_policy=monotonicity_policy,
        )

    def _models(
        self,
        *,
        phase2=None,
        phase3=None,
        phase4=None,
        phase5=None,
    ):
        return {
            "phase2_worse": ConstantModel(phase2 if phase2 is not None else [0.8, 0.8]),
            "phase3_worse": ConstantModel(phase3 if phase3 is not None else [0.7, 0.1]),
            "phase4_worse": ConstantModel(phase4 if phase4 is not None else [0.1, 0.1]),
            "phase5_worse": ConstantModel(phase5 if phase5 is not None else [0.1, 0.1]),
        }


if __name__ == "__main__":
    unittest.main()
